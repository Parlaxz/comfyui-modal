# Step 2 — manual toucher discriminator (T0 / T1 / T2)

## What was tested

Toucher = `st_touch_pages` from `/opt/source_touch.so`: native C, **one volatile load per guest
page**, no Python per-page loop, no payload copy, never calls `preadv`/`read`. One toucher
thread per reader process walks ahead in that reader's own lane. Consumer is the M0 C memcpy
into a preallocated private bytearray. Persistent mapping, 4 processes, QD4, 64 MiB,
4 ms floor, no rescue, no preadv payload path.

Interleaved by the predetermined schedule `[0,1,2,2,1,0]`. Counting rule: US only, singleton
US regions excluded. Artifacts: `step2b_touch/` (raw runs), `step2_touch/` (first attempt,
invalidated — see "Two invalidations" below).

## Result

| arm | counted n | GB/s median | mean | p10 | best | worst | wall median |
|---|---:|---:|---:|---:|---:|---:|---:|
| T0 no toucher | 2 | **5.295** | 5.295 | 5.166 | 5.457 | 5.134 | **1521** |
| T1 1 block ahead | 5 | 3.568 | 3.549 | 3.174 | 4.177 | 3.078 | 2255 |
| T2 2 blocks ahead | 7 | 3.717 | 3.512 | 2.687 | 4.512 | 2.115 | 2165 |

Consumer-operation tails:

| arm | ops | median | p95 | p99 | worst | ≥250 | ≥500 | ≥1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T0 | 240 | 48.96 | 66.68 | 87.18 | 90.9 | 0 | 0 | 0 |
| T1 | 600 | 69.46 | 131.66 | 150.73 | 659.9 | 2 | 1 | 0 |
| T2 | 840 | 62.12 | 144.13 | 492.96 | 1041.1 | 26 | 9 | 1 |

Toucher health (the toucher itself is a source consumer and can go sick):

| arm | touch events | touch median | touch p95 | touch max | ≥250 | ≥500 | ≥1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| T1 | 599 | 70.61 | 140.52 | 660.9 | 2 | 1 | 0 |
| T2 | 840 | 59.59 | 147.43 | **1045.5** | 28 | 8 | 1 |

## The mechanism — the toucher never got ahead

| arm | blocks paired | READY_AHEAD | CONSUMER_CAUGHT_TOUCHER |
|---|---:|---:|---:|
| T1 | 599 | **0** | 599 |
| T2 | 840 | **0** | 840 |

**In both arms the consumer caught the toucher on every single block.** The toucher never once
completed before the consumer arrived. So the toucher did not "move work earlier" — it ran
*concurrently* with the consumer against the same backing fetch, adding a second source
consumer for the same bytes.

That explains the result directly: T1/T2 do not add useful parallelism, they add contention.
Throughput falls ~30%, wall rises ~42–48%, and tails get *worse*, not better (T2 produced 26
operations ≥250 ms where T0 produced none).

## Gate decision

The gate was: close the branch unless T1 or T2 convincingly improves **total source wall,
low-end consistency, or tail incidence**.

- **T1 vs T0:** median GB/s **−32.6%**, wall median **+48.3%**
- **T2 vs T0:** median GB/s **−29.8%**, wall median **+42.3%**
- Low-end consistency: T1 p10 3.174, T2 p10 2.687 vs T0 5.166 — **worse**
- Tail incidence: T1 2 ops ≥250 ms, T2 26 ops ≥250 ms vs T0 **0** — **worse**

**The toucher branch is CLOSED.** Neither depth helps; both hurt materially. Per instruction,
no further depths were added and Step 7 (toucher + zero-copy) is **not run**, because its
gate (Step 2 must prove T1 or T2 helps end-to-end) did not pass.

## Two invalidations I had to correct

1. **First attempt (`step2_touch/`) was invalid.** The toucher recorded **0 touch events** in
   T1/T2 — an off-by-one meant `lead = touch_pos − consumer_pos` was never in `(0, touch_ahead]`,
   so the toucher never ran. The apparent T1 "+16.8%" in that run was **not a toucher effect**.
   Fixed by initialising `consumer_pos` to −1, setting it to the claimed index, and using the
   true lead `tp − cp`.
2. **Only after the fix** did the toucher actually execute (T1 839 events, T2 960 in the
   corrected batch), and only then does the real result appear — and it is negative.

## Honest limitations

- **T0 counted n = 2** in this cohort. The T0 arm is thin, so the *magnitude* of the penalty is
  not tightly estimated. However the direction is large (−30%), consistent across T1 and T2, and
  has a clean mechanistic explanation (READY_AHEAD = 0), so the gate decision is not sensitive to
  T0's sample size.
- **The A/B question ("does touching a page materially accelerate a subsequent full-block
  memcpy?") could not be answered here**, because READY_AHEAD was 0 — the touch never completed
  first, so there is no observation of "touch finished, then memcpy ran" to compare against a
  plain memcpy. This is reported as unanswerable from this data rather than inferred.
- Region composition: the toucher arms landed on a different region mix than T0, so part of the
  magnitude may be placement. The mechanistic evidence (READY_AHEAD = 0 plus the toucher's own
  ≥250 ms events) is what carries the conclusion, not the pooled number alone.
