# V2 D11 — Three-Run Cold Performance (25 s Gap Protocol)

Date: 2026-08-16 · Same deployment as the D11 first run (no redeploy; D1-primed identity `2305b0b3bbdf3fbe…`, runtime shape 12 CPU / 32768 MiB, TBASE, O0, fingerprint `f504e296c398bdcb2c4c07e2`)
Wrapper: `run_v2_single.bat --conditioning-cache-nonce <fresh uuid>` under `V2_D10_INTEGRATION_VALIDATION=1`, `V2_BENCHMARK_RUNS=1`
Gap protocol: 25-second Modal scaledown gap enforced between runs 5 and 6 (and attempted run 3 was discarded — see below)

## Run IDs and Logs

| Run | Request ID | Instance | Provider / Region | Nonce | Log |
|---|---|---|---|---|---|
| 2 | v2-benchmark-0-8ce2b1d3ce62 | 0be452a1e36849119fae580147c21faa | GCP / us-east4 | `0342df34-3330-4abb-98cb-87273d21e85b` | v2_d11_request_2.log |
| 5 | v2-benchmark-0-f397baff019f | 3afcf0b4eab247ec9a63e349e212e34e | GCP / us-east4 | `88ce0bf7-2c24-4483-bcda-f9a1d3cd1aa7` | v2_d11_request_5.log |
| 6 | v2-benchmark-0-54a4ff16625d | d2c9879a001c4011b1086ce615d54fc9 | **AWS / us-east-1** | `f1669331-310a-411e-986d-ebd6832aa863` | v2_d11_request_6.log |

All three: `FINAL_REQUEST_PREFLIGHT=PASS`, `Fresh: YES`, `restore_count=1`, `request_count=1`, `decision=miss_stored`, `CLIP encode (1 calls)`.

---

## Headline Times

| Metric | Run 2 | Run 5 | Run 6 | Mean |
|---|---|---|---|---|
| Command → response (bat window) | 25.247 s | 24.124 s | 24.853 s | 24.741 s |
| Command → response (reconciled) | 20.744 s | 20.407 s | 21.082 s | 20.744 s |
| Command minus scheduling | 17.627 s | 17.647 s | 18.063 s | 17.779 s |
| Modal scheduling | 3.117 s | 2.760 s | 3.018 s | 2.965 s |

---

## Cold-Start Waterfall — Key Stages

| Stage | Run 2 | Run 5 | Run 6 | Mean |
|---|---|---|---|---|
| 1. Modal pre-Python snapshot restore | 2.702 s | 2.600 s | 1.383 s | 2.228 s |
| 2. Python/application restore | 223.8 ms | 458.9 ms | 350.3 ms | 344.3 ms |
| 3. Restore-to-method entry | 18.0 ms | 20.6 ms | 24.5 ms | 21.0 ms |
| 4. Remote method setup | 1.722 s | 1.493 s | 1.454 s | 1.556 s |
| 5. PromptExecutor/cache setup | 10.1 ms | 139.6 ms | 6.9 ms | 52.2 ms |
| 6. Pre-sampler execution | 6.253 s | 6.272 s | 7.746 s | 6.757 s |
| 7. Sampler node to sampling | 124.1 ms | 129.7 ms | 155.1 ms | 136.3 ms |
| 8. Sampling | 4.758 s | 4.704 s | 4.937 s | 4.800 s |
| 9. Post-sampling / VAE transition | 912.1 ms | 922.0 ms | 1.052 s | 962.0 ms |
| 10. VAE decode | 364.8 ms | 371.4 ms | 439.9 ms | 392.0 ms |
| 12. Remote result handoff | 244.5 ms | 267.3 ms | 180.9 ms | 230.9 ms |
| Reconciliation | OK | OK | OK | — |

Note: stage 5 collapsed to milliseconds in these runs because the signature/cache machinery hot-paths; the conditioning decision is still a true `miss_stored` per fresh nonce.

---

## Model / Cache / Output Detail

| Metric | Run 2 | Run 5 | Run 6 |
|---|---|---|---|
| Cache decision | miss_stored | miss_stored | miss_stored |
| Lookup wall | 0.971 ms | 1.054 ms | 2.350 ms |
| Manifest entries | 64 | 64 | 64 |
| CLIP encode calls | 1 (6.151 s) | 1 (6.173 s) | 1 (7.465 s) |
| Sampling duration | 4.758 s | 4.704 s | 4.937 s |
| PNG encode / compress | 176.5 / 170.6 ms | 156.7 / 150.2 ms | 187.9 / 179.1 ms |
| Image | 1088×1920 · 3,129,718 B | same | same |
| Output SHA | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` | identical | identical |
| Peak RSS | 34.85 GiB | 34.85 GiB | 34.90 GiB |

Deterministic: identical output bytes and SHA across all three runs (same workflow, fresh nonce only isolates the cache key).

---

## Integrity / Protocol Notes

- Bat exit codes: 2 → 0, 5 → 0, 6 → 0. Preflight PASS (target match, runtime-shape fingerprint parity, D1 coverage, RUN_COUNT=1) printed by the bat before every submission.
- **Discarded measurements**: the chained attempt run 3 completed in 13.482 s on a warm container (no gap; user-flagged invalid, not counted) and run 4 was aborted mid-submission (incomplete log, `persistent_hit`; not counted).
- 25 s gap protocol applied before runs 5 and 6. Use of Modal scheduling: after ~9 min of idle before run 2 it was already cold; runs 5/6 enforce the stated policy.
- Provider pinning note: run 6 landed on AWS/us-east-1 (transport unpinned); stage-1 modal restore was faster there (1.383 s) while CLIP encode was slower (7.465 s).