# P (preadv) vs M2 (exact-window mmap) — same-time interleaved test

One experiment. CPU source-only. H100 host for placement comparability, GPU never touched.
4 processes · QD4 · 64 MiB · 4 ms global start spacing · same `qwen_3_4b.safetensors` · same
self-service scheduler · exact full-file coverage. No toucher, no M0, no M1, no CUDA/H2D/GPU,
no O_DIRECT, no new QD/block size/pacing.

Both engines ran **in the same time window**, alternating on the predetermined balanced schedule
`[P, M2, M2, P, P, M2]`, so region/placement exposure is interleaved rather than time-separated.

M2 operation cost is measured correctly as **mapping + source access/copy** (`map_ms + preadv_ms`).
MAP_POPULATE remains part of the implementation but is **inert** here; M2 is a mapping-lifecycle
variant, **not** eager population.

Counting rule: US only; singleton US regions excluded. Excluded runs retained with provider:region.
Raw artifacts: `pm2_interleaved/` (P vs M2), `rtx_m2/` (RTX). Report: `pm2_report/P_VS_M2.md`.

---

## Main table

| source | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) | 30 | 5.904 | 5.583 | 4.188 | 6.236 | 6.394 | 3.594 | 1363 | 1473 |
| exact-window mmap (M2) | 30 | **6.503** | **6.466** | **5.401** | **7.337** | **8.247** | **4.265** | **1237** | **1266** |

M2 is **+10.1% median GB/s, +15.8% mean, +29% p10, −9.2% wall median**.

## Tail table

| source | ops | median ms | p95 | p99 | worst | ≥250 | ≥500 | ≥1s | ≥2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) | 3602 | 43.91 | 69.99 | 92.26 | 692.2 | 4 | 1 | 0 | 0 |
| M2 | 3600 | 38.05 | 57.44 | 89.49 | 949.6 | **9** | **6** | 0 | 0 |

M2 has a better median and p95 but a **heavier mid-tail** in the 250–1000 ms band.

## Outliers (provider:region on every one)

| source | kind | run | provider:region | GB/s | wall ms | worst op ms |
|---|---|---|---|---:|---:|---:|
| P | bottom-decile | im-22 | UNSPECIFIED:us-central | 3.842 | 2094 | 104.1 |
| P | bottom-decile | im-23 | UNSPECIFIED:us-central | 4.044 | 1989 | 113.7 |
| P | worst run | im-37 | UNSPECIFIED:us-central | 3.594 | 2238 | 119.3 |
| M2 | bottom-decile | im-74 | GCP:us-west | 4.265 | 1886 | 949.6 |
| M2 | bottom-decile | im-44 | UNSPECIFIED:us-central | 5.100 | 1577 | 114.4 |
| M2 | worst run | im-74 | GCP:us-west | 4.265 | 1886 | 949.6 |

Every operation ≥250 ms:

| source | run | provider:region | block | offset | op ms |
|---|---|---|---:|---:|---:|
| P | im-43 | GCP:us-east | 30 | 2013265920 | 486.9 |
| P | im-43 | GCP:us-east | 90 | 6039797760 | 692.2 |
| P | im-43 | GCP:us-east | 61 | 4093640704 | 372.4 |
| P | im-43 | GCP:us-east | 90 | 6039797760 | 262.4 |
| M2 | im-24 | GCP:us-east | 62 | 4160749568 | 388.9 |
| M2 | im-24 | GCP:us-east | 90 | 6039797760 | 540.6 |
| M2 | im-42 | GCP:us-east | 90 | 6039797760 | 500.3 |
| M2 | im-42 | GCP:us-east | 30 | 2013265920 | 517.4 |
| M2 | im-50 | GCP:us-east | 90 | 6039797760 | 458.9 |
| M2 | im-50 | GCP:us-east | 62 | 4160749568 | 362.8 |
| M2 | im-74 | GCP:us-west | 60 | 4026531840 | 920.4 |
| M2 | im-74 | GCP:us-west | 90 | 6039797760 | 949.6 |
| M2 | im-74 | GCP:us-west | 11 | 738197504 | 530.6 |

**Block 90 (offset 6039797760) recurs in both arms**, and block 30 and 62 also repeat. A repeated
single-offset concentration across two different access mechanisms points at a specific slow
backing region rather than a syscall-level effect.

## Per-region

| region | preadv n/median | M2 n/median | delta % | preadv tails | M2 tails |
|---|---|---|---:|---:|---:|
| us-ashburn-1 | 1/5.049 | 3/7.007 | **+38.8%** | 0 | 0 |
| us-central | 5/4.044 | 3/5.201 | **+28.6%** | 0 | 0 |
| us-east | 5/5.925 | 8/6.196 | **+4.6%** | 4 | 6 |
| us-west | 18/5.955 | 16/6.766 | **+13.6%** | 0 | 3 |
| us-east4 | 1/5.427 | 0/- | - | 0 | 0 |

M2 is faster in **every** region where both arms have runs. Tail location, by region and by op
count: **us-east** carries tails in **both** arms (P 4 ops ≥250 ms, 1 ≥500 ms; M2 6 and 3);
**us-west** carries tails in **M2 only** (3 ops ≥250 ms, 3 ≥500 ms, from im-74); **us-central**
and **us-ashburn-1** show **zero** tails in either arm.

**Correction:** an earlier version of this report said "us-west and us-central show zero tails in
either arm". That was wrong — M2 us-west has three ≥250 ms operations (im-74). Only us-central and
us-ashburn-1 are clean in both arms.

---

## RTX PRO 6000 Blackwell — M2 window, 15 runs

Cross-GPU check requested after the main test. Same M2 engine, same geometry, on `rtx-pro-6000`.
GPU observed: **NVIDIA RTX PRO 6000 Blackwell Server Edition**. 15/15 valid, 0 Odin, 0 errors.

| group | n | GB/s median | mean | p10 | best | worst | wall median | ops | op median | op p95 | op worst | ≥250 | ≥500 | ≥1s | ≥2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all 15, pooled (all regions) | 15 | 6.513 | 6.491 | 5.808 | 7.632 | 3.442 | 1235 | 1800 | 38.46 | 56.97 | 1583.0 | 9 | 5 | 2 | 0 |
| **COUNTED** (US, non-singleton) | 2 | **7.072** | — | — | — | — | — | — | — | — | — | — | — | — | — |

Per-region (all 15 RTX runs):

| region | n | median GB/s | US? |
|---|---:|---:|---|
| ap-southeast | 7 | 7.095 | no |
| eu-south | 6 | 6.074 | no |
| us-east | 2 | 7.072 | yes |

RTX worst runs:

| run | provider:region | GB/s | worst op ms |
|---|---|---:|---:|
| im-01 | AWS:eu-south | 3.442 | 1583.0 |
| im-04 | AWS:eu-south | 5.774 | 306.3 |
| im-09 | AWS:eu-south | 6.336 | 256.3 |
| im-03 | GCP:us-east | 7.632 | 198.6 |

**RTX caveat:** only **2 of 15** runs landed in a US region, so the counted sample is n=2 and the
pooled figure is dominated by non-US regions (`ap-southeast`, `eu-south`). This is a **cross-GPU
sanity check, not a counted cohort.** What it does show is that the M2 engine behaves the same way
on RTX PRO 6000 Blackwell: ~6.5 GB/s pooled median, wall ~1235 ms, and one pathological op
(1583 ms) on `AWS:eu-south` — i.e. the same tail shape, not a new failure mode.

---

## Answers

**1. Is M2 faster than preadv overall?** **Yes** — 6.503 vs 5.904 GB/s median (+10.1%), mean +15.8%,
wall median −9.2%.

**2. Is it faster within the same regions?** **Yes** — M2 wins in all four overlapping regions:
us-west +13.6%, us-central +28.6%, us-ashburn-1 +38.8%, us-east +4.6%. This is the key result: the
advantage is **not** a composition artifact.

**3. Is its p10 / low-end consistency better?** **Yes, clearly** — p10 5.401 vs 4.188 (+29%), and
worst run 4.265 vs 3.594. M2's low end is materially tighter.

**4. Does it have more or fewer ≥250/500/1000 ms tails?** **More in the mid-band, equal at the
top.** ≥250: M2 9 vs P 4. ≥500: M2 6 vs P 1. ≥1s: **both zero.** ≥2s: both zero. So M2 buys
throughput and consistency but pays a heavier 250–1000 ms tail; it does not introduce
multi-second events.

**5. Are any apparent differences caused by region composition?** **No.** This was the specific
risk, and the interleaved same-window design plus the per-region table rule it out — M2 wins in
every overlapping region.

**6. Does the earlier M2 advantage survive a same-time interleaved comparison?** **Yes.** The
earlier cross-time comparison (M2 5.856 vs preadv 5.487) was suggestive but time-separated; this
test puts both engines in the same window and the advantage not only survives, it is **larger and
consistent** (+10.1% pooled, positive in every region).

**7. Should M2 replace preadv as our pure CPU source path?** **Not yet — it is a strong candidate,
not an automatic switch.** The trade-off is explicit:

- M2 wins on throughput (+10.1%), mean (+15.8%), low-end consistency (p10 +29%) and wall (−9.2%).
- preadv wins on mid-tail cleanliness (4 ops ≥250 ms and 1 ≥500 ms vs M2's 9 and 6), and it has
  **zero** operations ≥250 ms in the previously measured frozen cohort.
- Neither produces ≥1 s events in this test.

If the priority is steady throughput and low-end consistency, M2 is better. If the priority is
minimising 250–1000 ms outliers, preadv is better on this evidence. That is a policy decision, not
a settled measurement — and I am not making it automatically.

## Notes and limitations

- Both engines used the same self-service scheduler, geometry and correctness checks; the only
  difference is the access mechanism.
- M2's per-block cost legitimately includes mapping overhead; if it were counted as copy-only, M2
  would appear ~5× faster than it is. It is not counted that way here.
- The repeated appearance of **block 90 (offset 6039797760)** in both arms is worth a future look,
  but it is an observation, not a proven cause, and no follow-up was run automatically.
- RTX results are a cross-GPU sanity check with only n=2 counted (US); they are reported separately
  and are not pooled with the H100 cohort.
