# TEST 1 — Freeze scope: conclusion

**Corpus:** 308 usable witness runs (salvaged, zero new runs), 102 reads ≥250 ms across 24 runs.
Longest pathological read: **8744.6 ms**.

## Result: no witness froze. None of A/B/C/D applies.

Across all 102 sick reads, every one of the five witnesses kept ticking at its normal cadence for the entire duration of the read.

| witness | median gap | p90 | max | vs preadv of 250–8745 ms |
|---|---:|---:|---:|---|
| reader Python (own worker) | 11.2 ms | 19.2 | **79.9 ms** | healthy |
| reader **native** pthread (own worker) | 10.0 ms | 10.2 | **19.1 ms** | healthy |
| other readers' Python (max) | 11.5 ms | 23.4 | 78.7 ms | healthy |
| control-process Python | 11.1 ms | 17.9 | 63.2 ms | healthy |
| control-process **native** | 10.0 ms | 10.7 | 22.3 ms | healthy |
| parent/coordinator Python | 11.1 ms | 19.2 | 69.0 ms | healthy |

Baseline (median of per-run median gaps) is 10.0 ms for native and 10.73 ms for Python canaries in every context — so the cadences above are the healthy cadence, not a suppressed one.

**Classification: `E_neither_froze` — 102/102 (100%).**

| class | meaning | count | share |
|---|---|---:|---:|
| E_neither_froze | no witness froze | 102 | 100% |
| A / B / C / D | (any freeze) | **0** | **0%** |

Example rows (full table in `TEST1_FREEZE_SCOPE.md`, raw in `test1_sick_reads.csv`):

| run | provider/region | worker | preadv dur | reader Py gap | reader native gap | control Py gap | control native gap | parent gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| im-01-invalid20 | unspecified:eu-north | 3 | 8744.6 | 11.3 | 10.0 | 11.7 | 10.7 | 11.2 |
| im-01-invalid12 | gcp:us-east | 2 | 5274.8 | 12.5 | 10.0 | 11.7 | 10.0 | 11.3 |
| im-01-invalid6 | unspecified:eu-north | 3 | 4808.8 | 11.5 | 10.0 | 11.0 | 10.0 | 11.1 |
| im-05-invalid12 | unspecified:eu-north | 3 | 4510.0 | 11.8 | 10.0 | 11.8 | 10.0 | 11.1 |
| im-01-invalid20 | unspecified:eu-north | 0 | 2992.5 | 11.3 | 10.0 | 11.7 | 10.0 | 11.1 |
| im-02-invalid29 | unspecified:eu-north | 0 | 2374.3 | 11.0 | 10.1 | 11.0 | 10.0 | 11.1 |
| im-04-invalid22 | gcp:us-east | 3 | 865.4 | 17.7 | 10.0 | 17.1 | 10.0 | 24.9 |
| im-05-invalid5 | gcp:us-east | 3 | 845.4 | 24.6 | 10.7 | 27.9 | 10.9 | 19.2 |

## What this means

**The multi-second `preadv` is genuine syscall service time, not a scheduling freeze.** During an 8.7-second read the owning process remained fully schedulable: its Python canary ticked every ~11 ms, its native pthread every ~10 ms, and every other context — sibling readers, an independent control process, and the parent — was equally healthy.

This kills the process-freeze explanation for the stall. It also means the earlier conclusion in `hedge_trace_runs/HEDGE_LATENCY_TRACE.md` ("process-wide thread freezing") **cannot be right as stated**, and I am flagging that rather than quietly superseding it.

## Contradiction that must be reconciled

| | previous turn (`HEDGE_LATENCY_TRACE.md`) | this turn (Test 1) |
|---|---|---|
| canary design | Python thread, `Event.wait(0.010)`, no I/O | same design (reader Py canary) |
| max canary gap | **1378.9 ms** | **79.9 ms** |
| during | `preadv` of 1616 ms | `preadv` of up to 8744.6 ms |
| process composition | reader process ran **hedge machinery**: coordinator + original thread + 3 hedge threads + shared `multiprocessing` pacer gate | reader process ran **main thread + 1 canary only** |
| topology | `_mw_hedge_child` | `_witness_reader_child` |

The two measurements disagree by ~17×, and the one structural difference is **the hedge machinery and its thread/lock load**. A plausible reading is that the earlier "freeze" was caused by our own hedge-path contention (3 hedge threads plus the coordinator spinning on the shared `multiprocessing` semaphore via `_mw_gate_launch`), not by the platform.

**That is a hypothesis, not a finding.** The cheap decisive test is to re-run the witness probe **with hedging enabled**: if the reader Py/native canary gaps jump back to hundreds of ms only when hedging is on, the freeze was self-inflicted. This is the single most valuable follow-up and it costs one small cohort.

## Consequences for Test 2

Test 1 changes Test 2's premise in a useful way. If nothing freezes, then a dedicated 5th hedge process **should** be able to launch near 250 ms — which makes Test 2 a genuine test of the topology rather than a rerun of a known failure. Test 2 remains unrun.

## Provenance / caveats

- Zero new runs: all 308 runs were salvaged from `witness_runs/*invalid*.json` after the validator-spam incident. They are `status=ok`, `physical_reads=120`, exact once-only coverage, and carry all five witnesses.
- Native canary decode assumed 16-byte `<qq` records at header offset 128, stopping at the first zero `wall`. It produced 10.00 ms medians with tight p90s in **all** contexts, which is a strong self-consistency check that the decode is correct.
- Provider is preserved as a covariate: the longest reads cluster on `unspecified:eu-north` (which is Modal's own, non-odin) and `gcp:us-east`; the pattern is identical in both.
- These runs are the **unhedged** witness topology, so they say nothing directly about hedge behaviour.
