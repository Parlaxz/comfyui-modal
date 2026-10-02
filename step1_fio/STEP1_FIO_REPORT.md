# Step 1 — fio cross-check (pvsync vs mmap)

Independent corroboration only. CPU-only Modal function, no GPU requested.

## Method

- Same file: `/root/models/text_encoders/qwen_3_4b.safetensors` (8044982048 bytes)
- Engines: `ioengine=pvsync` vs `ioengine=mmap` (both **synchronous**)
- **4 independent fio jobs, one per non-overlapping contiguous quarter** — concurrency comes
  from the 4 separate job processes, never from `iodepth`
- `bs=64m`, `rw=read`, `direct=0` (no O_DIRECT), `invalidate=0`, no write, no verify
- 29 blocks (1946157056 bytes) per job, offsets 0 / 2013265920 / 4026531840 / 6039797760
- Predetermined interleave, 5+5 required, 16 runs launched to reach 5 counted each

Artifacts: `step1_fio/fio-*.json`, `step1_fio/fio_rows.json`. Job file and exact command are
recorded inside every run JSON (`jobfile`, `command`).

## Counting rule applied

US regions only; a US region seen once in an arm is excluded from counted statistics.
Every run landed in exactly one of two regions: **us-east** or **eu-west**.

- `eu-west` is **non-US → excluded from counted** (retained: `fio-04, 06, 07, 08, 11, 12, 14, 18, 19, 20, 22, 25`)
- `ap-southeast` (fio-23) → non-US → excluded

## Counted results (us-east only — the single eligible US region)

| engine | counted n | GB/s values | median | mean | best | worst |
|---|---:|---|---:|---:|---:|---:|
| fio pvsync | 5 | 1.325, 1.178, 3.514, 4.230, 2.004 | **2.004** | 2.450 | 4.230 | 1.178 |
| fio mmap | 7 (first 5 used) | 3.043, 2.886, 3.212, 2.773, 2.835 | **2.967** | 2.969 | 3.212 | 2.773 |

**Within the matched region, fio mmap is ~48% faster than fio pvsync (2.967 vs 2.004 GB/s).**

## Why this matters — the first reading was wrong

An earlier region-blind reading of the first 10 runs suggested the opposite (pvsync 2.576 vs
mmap 1.795). That batch did not record provider/region, and once identity was captured and the
region rule applied, **the direction reversed**. This is the same region-composition trap that
falsely suggested a pacing effect in the earlier pacing cohorts: pooled numbers without region
stratification pointed the wrong way.

## Answers

1. **Does fio mmap beat fio pvsync?** **Yes**, within the matched region (2.967 vs 2.004 GB/s).
2. **Is the direction consistent with our custom harness?** **Yes.** Our harness has M0
   persistent mmap at 6.069 GB/s vs frozen preadv at 5.818 GB/s — same direction.
3. **Are differences large enough to matter?** Yes for fio (~48% within-region), and the
   absolute fio throughputs are far below our harness (2–4 GB/s vs ~6 GB/s), so fio is a
   corroborating direction check, not a replacement.
4. **Do fio tails show placement sensitivity?** Yes, strongly: the same engine on the same file
   ranges from 1.178 to 4.230 GB/s (pvsync) and 2.773 to 3.212 GB/s (mmap) across runs, and the
   non-US `eu-west` runs sit in a different band again. fio sees the same placement sensitivity
   our harness does.

## Caveats

- fio cannot be claimed cold: `invalidate=0` was used deliberately and fio's own cache
  invalidation is not treated as proof of coldness anywhere here.
- `bs=64m` with synchronous engines produces very different queueing from our 4-process
  self-service harness, so absolute numbers are not comparable — only direction is.
- n is small (5 counted per arm) by design; this is a cross-check, not a cohort.
