# TEST 2 — dedicated 5th hedge process (125 ms threshold): pipe fix verified, hedge still never wins

**Corpus:** `hedge_proc_125/` — 20 valid runs, **166 hedge triggers**, QD4, 64 MiB, global 4 ms pacer, no pinning.
Trigger threshold lowered from 250 ms to **125 ms** (at 250 ms only 1 of 32 runs triggered).

## 1. The pipe fix is VERIFIED

| check | result |
|---|---|
| local API fact | `Pipe(duplex=False)` → `(recv_end, send_end)`; `send` on a recv-only end raises `OSError` — exactly the old symptom |
| hedge process status | **ok** (was `error` on 32/32 before the fix) |
| hedge requests dispatched | **166** (was 4, all `OSError`) |
| hedge reads actually served | **166** (was 0) |
| **receive → hedge `preadv` enter** | **median 0.16 ms, max 54.37 ms** |
| hedge `preadv` duration | median 21.51 ms |
| hedge-process canary max tick gap | median 22.8 ms, p90 81.9, max **81.9 ms** |

So the 5th process is alive, parked, responsive, and **does not freeze** — its canary never gaps more than 82 ms. The transport works end to end.

## 2. But the hedge never wins: 0 / 166, median saved 0.00 ms

| run | provider/region | original ms | hedge trigger ms | receive→enter ms | hedge enter (rel orig) ms | hedge dur ms | winner | saved ms |
|---|---|---:|---:|---:|---:|---:|---|---:|
| im-05 | unspecified:odin | 4551.5 | 4553.1 | 0.17 | 4553.25 | 19.43 | original | 0.00 |
| im-05 | unspecified:odin | 2648.0 | 2649.8 | 0.17 | 2649.99 | 17.94 | original | 0.00 |
| im-05 | unspecified:odin | 1607.9 | 1610.3 | 0.27 | 1610.62 | 20.79 | original | 0.00 |
| im-15 | gcp:us-east | 1278.1 | 1279.0 | 0.27 | 1279.27 | 23.50 | original | 0.00 |
| im-05 | unspecified:odin | 1086.6 | 1088.1 | 0.16 | 1088.31 | 18.30 | original | 0.00 |
| im-15 | gcp:us-east | 492.7 | 496.1 | 0.35 | 496.48 | 28.41 | original | 0.00 |
| im-05 | unspecified:odin | 192.7 | 194.8 | 0.18 | 195.02 | 17.76 | original | 0.00 |
| im-05 | unspecified:odin | 39.6 | 127.0 | 0.15 | 127.12 | 19.29 | original | 0.00 |
| im-17 | oci:us-central | 34.0 | 127.9 | 0.16 | 128.03 | 29.24 | original | 0.00 |

(full 166 rows available in the run JSONs; the pattern is uniform)

## 3. Why it never wins — the trigger fires at the original's completion, not at the threshold

| measurement | median | max |
|---|---:|---:|
| **original enter → parent sends trigger** | **141.2 ms** | **4553.1 ms** |
| receive → hedge enter | 0.16 ms | 54.37 ms |
| hedge wins | **0 / 166** | — |

For **long** originals the trigger does not fire near the 125 ms threshold — it fires at **original + ~1.5–2 ms**:

- original 4551.5 ms → trigger at 4553.1 ms
- original 2648.0 ms → trigger at 2649.8 ms
- original 1607.9 ms → trigger at 1610.3 ms
- original 1278.1 ms → trigger at 1279.0 ms

That is the *same signature* as the threaded hedge in `HEDGE_LATENCY_TRACE.md` (hedge claim ≈ original completion), now reproduced with a completely different execution context.

**Prime suspect: the parent's trigger loop is single-threaded and blocks in `hedge_resp_recv.recv()` once per hedge.** While it waits for one hedge response it cannot poll the other readers, so dispatch serialises behind the slowest in-flight hedge and falls arbitrarily far behind. Supporting evidence:

- for **short** originals the trigger fires at ~126–160 ms (roughly on time), i.e. the loop is healthy when unloaded;
- for **long** originals it slips to original + ~2 ms, i.e. the loop is stalled for the whole duration of the slow read;
- `receive → enter` is sub-millisecond, so the transport itself is never the delay — the delay is entirely **before** the send.

Secondary contributor: the reader publishes `(block_index, enter)` per block but the parent keys its dedup on `block_index`, so a stale slot can be re-evaluated. This is not the dominant term but should be fixed.

## 4. Does Test 1 explain the result?

**Not directly, and that matters.** Test 1 showed nothing freezes — the hedge process's own canary confirms that (max gap 82 ms). So the failure is **not** a scheduling or freeze problem. It is a **dispatch-architecture** problem: one blocking, single-threaded trigger loop that serialises hedge launch behind in-flight hedges.

This also means the earlier "process-wide freezing" explanation in `HEDGE_LATENCY_TRACE.md` is now doubly unsupported — the same end-state appears with no freeze at all.

## 5. Conclusions

| question | answer |
|---|---|
| Does moving the hedge into a 5th process let it launch near 250 ms (or 125 ms)? | **No.** The transport is instant (0.16 ms) but the trigger does not fire until the original completes for long reads. |
| Does it actually rescue pathological reads? | **No.** 0/166 wins, 0 ms saved. |
| Does Test 1 explain the result? | **It rules out the freeze explanation.** The cause is the serialised parent dispatch loop, not scheduling. |

## 6. Caveats

- 5 of 20 runs landed on **`unspecified:odin`** (a non-odin-but-Modal-owned region) and one of them (`im-05`) produced the worst stalls. Provider is therefore a strong covariate here; the win/loss pattern is identical on `gcp` and `oci`, so the conclusion does not depend on it.
- The 125 ms threshold was chosen for event yield, not as the production value. At 125 ms the trigger lag is already visible; at 250 ms it would be worse.
- Fixing the dispatch loop (non-blocking send, one dispatcher per reader, or a dedicated trigger thread) is the obvious next step and is **not** implemented.
