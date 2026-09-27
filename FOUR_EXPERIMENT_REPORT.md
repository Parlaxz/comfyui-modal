# Four-experiment report — source-read scheduling and pathological-fetch recovery

Platform: gVisor, Modal H100, `/root/models/text_encoders/qwen_3_4b.safetensors` (8044982048 bytes).
Odin excluded from every count and retained separately. Provider + region preserved per run.

## Summary

| experiment | control | treatment | n | throughput result | tail result | verdict |
|---|---|---|---:|---|---|---|
| 1 self-service fast allocator | 42 static QD4/64 MiB (reused) | 42 self-service QD4/64 MiB | 42v42 | 5.818 vs 6.015 GB/s (−3.3%) | 0 reads ≥250 ms vs 2 | **manager bubble fixed**; −3.3% is provider mix |
| 2 split-range rescue | — | 2x64 and 4x32 on 128 MiB | 21 / 22 | — | 2x64 5W/5L; 4x32 1W/6L | **does not escape** |
| 3 mmap read paths | 42 self-service preadv (frozen) | M0/M1/M2, 64 MiB | 12 / 13 / 13 | M0 6.069, M1 5.954, M2 5.946 vs 5.818 | M0 max 443 ms, M1 813 ms, M2 6388 ms vs 220 ms | **M0 best on median, all worse on worst** |
| 4 prearmed O_DIRECT rescue | 42 frozen + 21 matched-128 MiB | 30 O_DIRECT rescue, 128 MiB | 30 | 5.655 GB/s, wall 1423 ms | logical max 6494.6 ms, 14 ≥1000 ms | **does not cap the tail** |

## Experiment 1 — self-service fast allocator

Telemetry audit first, zero new runs. The old manager allocator's per-block
`exit → next enter` gap was **1.4290 ms** against **0.0788 ms** for the coordination-free
static loop, so the manager-bubble premise was confirmed and the fix was built:
workers claim/gate/preadv/publish through tiny shared state
(`mp.Array(..., lock=False)` plus one explicit lock); the parent is on no per-block path.

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| self-service | 42 | 5.818 | 5.529 | 3.736 | 6.905 | 7.076 | 2.361 | 1383 | 1566 |
| static QD4/64 | 42 | 6.015 | 5.852 | 5.276 | 6.445 | 7.194 | 3.060 | 1337 | 1398 |

Per-block bubble: **0.1095 ms** (self-service) vs 0.0779 (static) vs 1.4290 (old manager) — an 18x cut,
now within 0.06 ms of the coordination-free loop. All 42 frozen runs clean: exact coverage,
maxQD 4, spacing ≥4 ms, amplification 1.0, zero errors.

## Experiment 2 — 2x64 vs 4x32 split rescue (128 MiB)

An interim claim of mine that this architecture produced zero ≥250 ms reads was **wrong**: it was a
lucky sample taken before a later batch landed. `exp2_2x64/im-28.json` reached an 8783 ms primary.

| arm | valid runs | eligible events | wins | losses |
|---|---:|---:|---:|---:|
| A: 2x64 | 21 | 10 | 5 | 5 |
| B: 4x32 | 22 | 7 | 1 | 6 |

Both arms fired the stopping rule. **Changing the request shape does not escape the pathological fetch.**
On 5166 ms and 8346 ms primaries the 2x64 rescue finished **0.03 ms and 0.48 ms** behind the original —
a photo-finish tie. 4x32 was worse. Subranges stall together with the original.

## Experiment 3 — mmap read paths

Prior art was audited first and the naive path avoided: `benchmark_source_io_e14.py` sliced the mapping
(`mapping[pos:pos+count]`), materialising a Python bytes object per block. All arms here use a C-level
`memcpy` into a preallocated destination.

| method | n | GB/s median | mean | p10 | p90 | best | worst | wall median | worst block |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv control | 42 | 5.818 | 5.529 | 3.736 | 6.905 | 7.076 | 2.361 | 1383 | 220.5 |
| M0 persistent mmap + memcpy | 12 | 6.069 | 6.183 | 5.431 | 7.174 | 7.218 | 4.627 | 1328 | 443.4 |
| M1 + MADV_WILLNEED | 13 | 5.954 | 5.949 | 4.504 | 7.425 | 7.956 | 3.970 | 1351 | 813.0 |
| M2 exact-window MAP_POPULATE | 13 | 5.946 | 5.668 | 4.625 | 7.353 | 7.546 | 0.126 | 1353 | 6387.7 |

M0 is the best arm on median and much more consistent on the low end (p10 5.431 vs 3.736), but every
mmap arm has a worse worst-case than the control. M2 merely *relocates* cost: copy drops to 7.2 ms
because MAP_POPULATE pre-populates, but map/populate costs 33.2 ms — the same total as M0's 43 ms copy.
**Fault deltas are not trustworthy here:** gVisor reports `minflt`/`majflt` as exactly 0 for all readers
across 120 x 64 MiB paged reads, so they are reported unavailable rather than as zeros.

## Experiment 4 — prearmed O_DIRECT QD5 rescue (128 MiB)

Healthy path preserved: the spare took **zero** normal work (`reader_blocks_won [15,15,15,15,0]`),
amplification median 1.0000, max physical inflight median 4.0 / max 5 (transient only),
min spacing for buffered workers **4.0001 ms**, exact coverage 30/30, 0 worker errors,
0 O_DIRECT errors, 0 exact mismatches.

**The lifetime rule worked:** spare promoted 5x, refilled 5x, 11 role flips — no
slot_busy/loser-capacity loss, unlike the historical bug.

| run | provider/region | primary ms | O_DIRECT ms | winner | ms saved |
|---|---|---:|---:|---|---:|
| im-02 | GCP:us-west | 507.8 | 258.3 | rescue | 3.51 |
| im-06 | OCI:us-central | 317.5 | 144.8 | primary | - |
| im-06 | OCI:us-central | 340.7 | 97.1 | primary | - |
| im-06 | OCI:us-central | 265.0 | 65.3 | primary | - |
| im-07 | UNSPECIFIED:eu-north | **5280.6** | **5043.9** | **primary** | - |
| im-07 | UNSPECIFIED:eu-north | 2554.2 | 1770.0 | primary | - |
| im-07 | UNSPECIFIED:eu-north | 1669.4 | 38.6 | primary | - |
| im-07 | UNSPECIFIED:eu-north | 1185.1 | 216.8 | rescue | 2.61 |
| im-07 | UNSPECIFIED:eu-north | 2234.0 | 1979.3 | primary | - |
| im-07 | UNSPECIFIED:eu-north | 402.5 | 154.9 | primary | - |
| im-07 | UNSPECIFIED:eu-north | 397.8 | 147.6 | primary | - |
| im-22 | GCP:us-west | 479.0 | 229.6 | primary | - |
| im-22 | GCP:us-west | 543.2 | 58.8 | rescue | 13.42 |
| im-24 | GCP:us-west | 544.7 | 291.8 | rescue | 7.69 |
| im-24 | GCP:us-west | 472.9 | 137.1 | rescue | 0.00 |
| im-28 | GCP:us-west | 573.3 | 326.6 | rescue | 0.58 |
| im-38 | GCP:ap-south | **4520.3** | **4277.3** | **primary** | - |
| im-38 | GCP:ap-south | 4536.7 | 34.4 | primary | - |

18 attempts, 6 wins, 12 losses. **O_DIRECT does not escape the stall.** When the buffered primary
stalls for seconds, O_DIRECT stalls with it (5043.9, 1979.3, 1770.0, 4277.3 ms). Because O_DIRECT
bypasses the page cache entirely, this locates the stall **below** the page cache, in the underlying
fetch — not in cache behaviour. The only wins were on sub-second stalls.

## The four experiments, in one line each

1. The manager round-trip was real (~1.43 ms/block) and is fixed (0.11 ms), at −3.3% pooled throughput
   that provider stratification attributes to provider mix, with a *better* tail than static.
2. Splitting a 128 MiB request into 2 or 4 subranges does not escape a pathological fetch.
3. Persistent mmap + C-level memcpy (M0) is the best alternate path on median and consistency, but no
   mmap arm improves the worst case; MAP_POPULATE is actively dangerous.
4. A prearmed O_DIRECT spare on a correct lifetime rule does not cap the tail either — and points at
   the stall being below the page cache.

## Corrections made during this work

- I reported "zero ≥250 ms reads" for the self-service architecture from an incomplete sample. That was
  wrong; the user caught it. Stalls are common at 128 MiB.
- I fixed a real bug that run exposed: `subread_ms` was not reset between successive rescues by one
  worker, so the list accumulated. It never affected reads, geometry, winner, or timing.
- `ctypes.from_buffer()` requires a *writable* buffer, so it rejected an `ACCESS_READ` mmap; the
  persistent mapping is now taken through libc. Reader setup failures also now surface immediately
  instead of after a 300 s barrier timeout.

## Artifacts

`exp1_telemetry/DECOMPOSITION.md` · `exp1_control_frozen/EXP1_REPORT.md` · `exp2_report/EXP2_REPORT.md` ·
`exp3_report/EXP3_REPORT.md` · `exp4_report/EXP4_REPORT.md` · raw runs in `exp1_control_frozen/`,
`exp2_2x64/`, `exp2_4x32/`, `exp3_m0/`, `exp3_m1/`, `exp3_m2/`, `exp4_odirect/` (Odin retained in place).

No fifth experiment was started.
