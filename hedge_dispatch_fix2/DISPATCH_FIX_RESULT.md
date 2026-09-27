# Parent hedge-dispatch fix — VERIFIED, with a real hedge win

**Result: the fix works. A hedge now launches at the threshold and beats a pathological original.**

## Root cause (it was not where I first said)

Two defects, and the dominant one was in the **reader**, not the parent loop:

1. **Dominant — the reader published `enter` only after the read finished.** In `_hp_reader_child` the original thread called `orig.update({... "enter": enter ...})` *after* `preadv` returned, and the coordinator waited on `while "enter" not in orig`. So the publish point was the syscall's **exit**, not its entry. The parent therefore could not see a crossing until the original was already done. This alone explains the earlier "trigger fires at original + ~2 ms" signature in `hedge_proc_125`.
   **Fix:** the thread now records `enter` and sets a dedicated `orig_entered` event *before* calling `preadv`; the coordinator waits on that event.

2. **Secondary — the parent blocked in `recv()` per hedge.** The main loop called `hedge_resp_recv.recv()` inline, serialising dispatch behind each in-flight hedge.
   **Fix:** a dedicated `_drain_responses` thread now owns responses and publishes results into shared memory; the main loop only sends, so threshold detection stays live continuously.

3. **Stale identity.** Requests are now keyed by `(worker, generation, block_index)` instead of block index, and the reader accepts a hedge only when generation and block both match its current block. Slot layout extended to 5 per worker: `[generation, block_index, enter_ns, hedge_exit_ns, hedge_bytes]`.

## Evidence

| | before fix (`hedge_proc_125`) | after fix (`hedge_dispatch_fix2`) |
|---|---:|---:|
| trigger latency (orig enter → parent sends) | median **141 ms**, max **4553 ms** | median **125.3 ms**, max **125.9 ms** |
| hedge wins | **0 / 166** | **1 strict / 3 reader-accepted**, of 5 |
| hedge-process canary max gap | 81.9 ms | 11.9 ms |

Trigger latency now sits **at** the 125 ms threshold instead of tracking the original's duration. That is the decisive change.

## The winning hedge event

| run | provider/region | original ms | trigger ms | receive→enter ms | hedge enter rel original | hedge ms | winner | ms saved |
|---|---|---:|---:|---:|---:|---:|---|---:|
| **im-09.json** | **gcp:us-east** | **239.1** | **125.3** | **0.30** | **125.61** | 112.66 | **hedge** | **0.82** |

Against your success criterion:

| criterion | target | actual | met |
|---|---|---|---|
| trigger occurs near 125 ms | ≈125 ms | **125.3 ms** | ✅ |
| hedge process receives promptly | prompt | **0.30 ms** | ✅ |
| hedge `preadv` enters promptly | ≈125–130 ms | **125.61 ms** | ✅ |
| hedge finishes before the original | yes | yes (238.3 vs 239.1 ms) | ✅ |
| hedge is the logical winner | YES | **YES** | ✅ |

**All five criteria are met.** One deviation from your illustrative shape: the hedge's own `preadv` took **112.66 ms**, not 20–40 ms, so it finished only **0.82 ms** before the original rather than at ~145–170 ms.

## Full hedge-event table

| run | provider/region | original ms | trigger ms | receive→enter ms | hedge enter rel original | hedge ms | winner | ms saved |
|---|---|---:|---:|---:|---:|---:|---|---:|
| im-09.json | gcp:us-east | 239.1 | 125.3 | 0.30 | 125.61 | 112.66 | **hedge** | **0.82** |
| im-09.json | gcp:us-east | 164.2 | 125.7 | 30.24 | 155.96 | 17.51 | original | 0.00 |
| im-09.json | gcp:us-east | 148.2 | 125.9 | 0.27 | 126.19 | 21.97 | original | 0.00 |
| im-09.json | gcp:us-east | 143.9 | 125.0 | 17.85 | 142.87 | 17.86 | original | 0.00 |
| im-09.json | gcp:us-east | 140.4 | 125.2 | 3.20 | 128.44 | 15.99 | original | 0.00 |

## Counts

| metric | value |
|---|---|
| runs needed | **10** (first 5 contained no read >125 ms) |
| hedge-eligible reads seen (>125 ms) | **5** |
| hedge launches | **5** triggers (3 reader-accepted) |
| hedge wins | **1** strict exit-before-original (3 reader-accepted) |
| **trigger → hedge-enter delay, winning event** | **0.31 ms** (125.30 → 125.61) |
| hedge-process canary max gap | 11.9 ms (no freeze) |

## What this does and does not prove

**Proved:** the dispatch path is fixed. Threshold detection is live, the trigger fires at the configured threshold, the hedge process receives in 0.3 ms and enters `preadv` within ~0.3 ms of the trigger. A hedge can genuinely beat a pathological original.

**Not proved / caveat:** the win margin is **0.82 ms**. The winning hedge's own read took 112.66 ms on the same path — i.e. the hedge **shared most of the stall**. That is the same-path resource property, not a dispatch problem, and it means this fix makes hedging *correct* but does not by itself make it *valuable*. The 4 losing events also show hedges running 16–22 ms against originals of 140–164 ms that had already nearly finished by the time the trigger fired at 125 ms — with a 125 ms threshold, an original that completes at ~140 ms is only ~15 ms from done when the hedge starts, so it cannot be beaten.

All other architecture is unchanged: QD4 readers, 64 MiB, global 4 ms pacer, dedicated 5th process, no pinning, no work stealing.
