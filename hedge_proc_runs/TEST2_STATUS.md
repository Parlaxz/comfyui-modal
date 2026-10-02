# TEST 2 — dedicated 5th hedge process: NO USABLE RESULT (engine bug)

**Verdict: invalid. Do not use these 32 runs for anything except the bug diagnosis below.**
Test 2 did **not** produce hedge data, so none of the three Test 2 conclusions can be answered yet.

## What happened

| quantity | value |
|---|---|
| runs collected | 32 (`hedge_proc_runs/im-*.json`) |
| `hedge_process_status` | **`error` on 32 / 32** |
| hedge reads actually served | **0** |
| hedge triggers recorded | 4 |
| trigger errors | `OSError` ×4 |
| hedge accepts (wins) | 0 |
| runs containing a logical read >250 ms | **1 / 32** (worst 499.0 ms) |
| median GB/s | 5.825 |

So: the primary QD4 path ran fine (median 5.83 GB/s, 32/32 complete, exact coverage), but **the hedge process never worked at all**.

## Root cause — my bug, one line

`multiprocessing.Pipe(duplex=False)` returns **`(recv_end, send_end)`**. I assigned them backwards:

```python
# WRONG (what I wrote):
hedge_req_parent, hedge_req_child = pacer_ctx.Pipe(duplex=False)   # parent got the RECV end
hedge_resp_child, hedge_resp_parent = pacer_ctx.Pipe(duplex=False) # child got the RECV end
```

The parent then called `hedge_req_parent.send(...)` on a **receive-only** connection → `OSError`, and the hedge process called `resp_conn.send(...)` on a receive-only end → its own `error` status. Hence 4 triggers, 0 served, and `hedge_process_status=error` on every run.

**Fixed** in `run_worker_model_hedge_process_probe`:

```python
hedge_req_recv,  hedge_req_send  = pacer_ctx.Pipe(duplex=False)  # child recv, parent send
hedge_resp_recv, hedge_resp_send = pacer_ctx.Pipe(duplex=False)  # parent recv, child send
```

Compiles clean; **not yet verified by a run.**

## Why a re-run needs a bigger cohort

Only **1 of 32** runs contained a read >250 ms. At that rate, reaching the requested ≥10 hedge-eligible reads needs roughly **300 runs**. Two options:

1. Accept a smaller n (e.g. 3–4 hedge events from ~120 runs) and report it as under-powered.
2. Lower the trigger threshold for the diagnostic (e.g. 100 ms) so more reads qualify — but that changes what is being tested.

## A separate, important observation

The 30-run hedge-process cohort landed almost entirely on fast providers (`gcp` 24, `oci` 3, `unspecified` 3, `azure` 2) and produced **one** read above 250 ms. Combined with Test 1, this reinforces that the pathological stall is **rare and provider-correlated**, not a property of the architecture under test.

## Status of the three Test 2 questions

| question | answer |
|---|---|
| Does a 5th process let the hedge launch near 250 ms? | **unknown** — no hedge ever ran |
| Does it actually rescue pathological reads? | **unknown** |
| Does Test 1 explain the result? | **unknown** — but Test 1 says nothing freezes, so a 5th process *should* be able to launch on time, which makes this a real test once the pipe bug is fixed |
