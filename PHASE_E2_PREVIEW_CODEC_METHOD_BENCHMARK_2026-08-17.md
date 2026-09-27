# Phase E2 Preview Codec Method Benchmark

Date: 2026-08-17 (run executed 2026-08-22 local)  
Scope: local CPU codec-only characterization of the WebP **encoder effort/method** axis at fixed quality 70  
Lane: parallel read-only investigation; no production changes, no deployment, no Modal call, no GPU spend, no commit

## Verdict

Encoder effort/method — not codec or quality — is the dominant latency lever for
the lossy Preview path. At fixed WebP q70 on the real production callable,
dropping Pillow/libwebp `method` from the current production value **4** to
**0** cut target-size encode time by **3.25x–5.88x** across all three
target-size inputs while changing decoded quality by at most **-0.62 dB PSNR**
(and effectively 0 dB on high-detail content). On realistic image statistics
(d7r2-derived 1088x1920) method 0 measured **54.500 ms median / 69.750 ms p95**
(classification A, comfortably under both the <100 ms preferred and <135 ms
practical targets); the smooth gradient measured **62.000 ms median /
78.000 ms p95** (A). Only the pathological uniform-random-noise stress case
remains over budget at **187.500 ms median / 225.200 ms p95** (C), improved
from 609.500 ms at method 4.

Best candidate: **method 0**, judged on (1) lowest latency in every case,
(2) all samples decodable, (3) no material quality regression at fixed q70,
(4) modest size increase on realistic content (+32.9%) and none on noise
(-1.0%). Method 1 is the conservative fallback (2.59x-4.11x, +27.8% size on
realistic content). Method 2 is dominated by method 1 (slower, and +57.6%
size on noise).

Classification summary (worst case across target-size inputs):

| Method | Worst median ms | Worst p95 ms | All decodable | Class |
|---:|---:|---:|---|---|
| 0 | 187.500 | 225.200 | True | C (A on gradient and realistic input) |
| 1 | 235.000 | 271.150 | True | C (B/A on gradient and realistic input) |
| 2 | 304.500 | 335.200 | True | C |
| 3 | 546.500 | 629.100 | True | C |
| 4 | 609.500 | 656.450 | True | C |
| 5 | 750.000 | 896.150 | True | C |
| 6 | 1078.000 | 1509.250 | True | C |

Per-case classes: A = median and p95 < 100 ms; B = median < 135 ms and
p95 < 150 ms; C = above B thresholds; D = decode failure (none occurred).

## 1. Source Inspection — exact current method for lossy Preview

The current production lossy Preview method is **4**, hardcoded:

- `comfyapp.py:303` — `_WEBP_LOSSY_METHOD = 4`
- `comfyapp.py:614` — `pil_img.save(out_buf, format="WEBP", lossless=False, quality=quality, method=_WEBP_LOSSY_METHOD)` (reached for normalized format `webp_lossy`; the Preview alias `"webp"` normalizes to `webp_lossy` per `contracts.py:412`, with `DEFAULT_PREVIEW_QUALITY = 70` at `contracts.py:407`)
- Duplicated converter path hardcodes the same value: `output_converter.py:42` (`_WEBP_LOSSY_METHOD = 4`) used at `output_converter.py:233`

Option-name mapping (`fast` / `balanced` / `max`):

- Allowed values: `_WEBP_LOSSLESS_COMPRESSION = ("fast", "balanced", "max")` (`comfyapp.py:301`, `contracts.py:404`), normalized by `normalize_webp_lossless_compression` (`contracts.py:484`)
- Mapping to Pillow `method`: `_WEBP_LOSSLESS_METHOD = {"fast": 0, "balanced": 4, "max": 6}` (`comfyapp.py:302`, mirrored in `output_converter.py:35`)
- **Critical finding:** this mapping is applied ONLY to the lossless branch
  (`output_format == "webp_lossless"` → `lossless=True`, `comfyapp.py:610-612`,
  `output_converter.py:212-223`). The lossy Preview branch ignores
  `webp_lossless_compression` entirely and always uses the constant 4.
  Therefore the existing contract does NOT currently expose a faster lossy
  mode; setting Preview to an existing faster mode would not suffice today.

## 2. Benchmark Method

The harness calls the real production function
`comfyapp.encode_image_tensor_batch(images_t, "webp", None, "balanced")` and
varies only the encoder effort by patching the module-level
`comfyapp._WEBP_LOSSY_METHOD` constant in-process per arm (restored to its
imported value 4 after every arm; asserted at exit). No production source
file was modified. Timing is the function's own `output_codec_ms` field —
the same production timing interval used by the prior E2 codec benchmark
(PIL save only; excludes tensor-to-NumPy, PIL construction, buffer reads,
decode validation, persistence, network).

All seven Pillow/libwebp lossy methods (0-6) were accepted by this build
(probed before the sweep). Quality fixed at 70 throughout. Each case x method
used 2 warmups followed by 12 measured repetitions. Every encoded sample was
decoded with Pillow; MSE/PSNR were computed against the source uint8 tensor
with NumPy only (no additional packages installed).

Cross-run note: this run's method-4 baseline drifted higher than the
2026-08-17 recorded run (gradient 305.000 vs 235.000 ms median; noise
609.500 vs 555.000 ms) — ordinary host-load variance between sessions. All
speedups below are computed within this single run, so they compare like
with like.

## 3. Inputs

| Case | Tensor | Input type | Details |
|---|---|---|---|
| `gradient-target` | `[1, 1920, 1088, 3]` uint8 | synthetic smooth gradient | identical generator to prior lane; 6,266,880 decoded bytes |
| `noise-target` | `[1, 1920, 1088, 3]` uint8 | deterministic high-detail noise | seed `20260817`, identical to prior lane; 6,266,880 decoded bytes |
| `d7r2-derived-target` | `[1, 1920, 1088, 3]` uint8 | real-image-derived target-size input | in-memory transform of preserved `d7r2-original-0.png`: RGB -> LANCZOS resize (3413, 1920) [3413 = round(1280 * 1920/720)] -> center crop (1162, 0, 2250, 1920) |

The derived input is NOT claimed to be the original production D7R2
resolution; it exists purely to carry realistic texture/statistics at the
target pixel count. No other preserved target-resolution generated images
were found, so the transform approach was used. Everything stayed in memory;
no files were written.

## 4. Environment

| Field | Value |
|---|---|
| Python | 3.11.9 |
| PyTorch | 2.8.0+cu128 |
| NumPy | 2.4.6 |
| Pillow | 11.2.1 |
| Platform | Windows-10-10.0.19045-SP0 |
| Processor | AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD |
| Logical CPUs | 12 |
| Callable source | `comfyapp.py` -> `encode_image_tensor_batch` |

## 5. Summary — per case x method (q70, 12 reps)

| Case | Method | Median ms | P95 ms | Min ms | Max ms | Median bytes | Ratio | MSE | PSNR dB | Decodable | Class |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| gradient-target | 0 | 62.000 | 78.000 | 31.000 | 78.000 | 11124 | 563.37x | 1.06 | 47.88 | True | A |
| gradient-target | 1 | 78.500 | 107.950 | 63.000 | 125.000 | 7966 | 786.70x | 1.02 | 48.06 | True | B |
| gradient-target | 2 | 94.000 | 125.000 | 62.000 | 125.000 | 7992 | 784.14x | 1.02 | 48.06 | True | B |
| gradient-target | 3 | 273.000 | 304.200 | 235.000 | 313.000 | 6660 | 940.97x | 0.92 | 48.50 | True | C |
| gradient-target | 4 | 305.000 | 328.450 | 250.000 | 329.000 | 6660 | 940.97x | 0.92 | 48.50 | True | C |
| gradient-target | 5 | 312.000 | 343.450 | 297.000 | 344.000 | 8240 | 760.54x | 1.00 | 48.14 | True | C |
| gradient-target | 6 | 265.500 | 297.000 | 203.000 | 297.000 | 6660 | 940.97x | 0.92 | 48.50 | True | C |
| noise-target | 0 | 187.500 | 225.200 | 156.000 | 234.000 | 1242124 | 5.05x | 3527.31 | 12.66 | True | C |
| noise-target | 1 | 235.000 | 271.150 | 218.000 | 297.000 | 1241718 | 5.05x | 3527.30 | 12.66 | True | C |
| noise-target | 2 | 304.500 | 335.200 | 250.000 | 344.000 | 1976748 | 3.17x | 3523.26 | 12.66 | True | C |
| noise-target | 3 | 546.500 | 629.100 | 515.000 | 672.000 | 1253340 | 5.00x | 3520.90 | 12.66 | True | C |
| noise-target | 4 | 609.500 | 656.450 | 531.000 | 657.000 | 1254562 | 5.00x | 3521.01 | 12.66 | True | C |
| noise-target | 5 | 750.000 | 896.150 | 625.000 | 922.000 | 1258958 | 4.98x | 3531.36 | 12.65 | True | C |
| noise-target | 6 | 1078.000 | 1509.250 | 1000.000 | 1578.000 | 1256056 | 4.99x | 3531.01 | 12.65 | True | C |
| d7r2-derived-target | 0 | 54.500 | 69.750 | 46.000 | 78.000 | 120376 | 52.06x | 9.79 | 38.22 | True | A |
| d7r2-derived-target | 1 | 78.000 | 93.000 | 62.000 | 93.000 | 115792 | 54.12x | 9.75 | 38.24 | True | A |
| d7r2-derived-target | 2 | 101.500 | 125.000 | 93.000 | 125.000 | 96118 | 65.20x | 10.15 | 38.07 | True | B |
| d7r2-derived-target | 3 | 367.500 | 437.450 | 297.000 | 438.000 | 90564 | 69.20x | 8.78 | 38.70 | True | C |
| d7r2-derived-target | 4 | 320.500 | 375.000 | 297.000 | 375.000 | 90590 | 69.18x | 8.52 | 38.83 | True | C |
| d7r2-derived-target | 5 | 313.000 | 429.200 | 297.000 | 438.000 | 92018 | 68.10x | 8.93 | 38.62 | True | C |
| d7r2-derived-target | 6 | 422.000 | 468.450 | 360.000 | 469.000 | 89566 | 69.97x | 8.78 | 38.70 | True | C |

## 6. Speedup vs current production method (4)

| Case | Method | Median ms vs m4 | Speedup | Bytes delta % | PSNR delta dB | Class |
|---|---:|---:|---:|---:|---:|---|
| gradient-target | 0 | 62.000 vs 305.000 | 4.92x | +67.0% | -0.62 | A |
| gradient-target | 1 | 78.500 vs 305.000 | 3.89x | +19.6% | -0.44 | B |
| gradient-target | 2 | 94.000 vs 305.000 | 3.24x | +20.0% | -0.44 | B |
| gradient-target | 3 | 273.000 vs 305.000 | 1.12x | +0.0% | +0.00 | C |
| gradient-target | 4 <- current | 305.000 vs 305.000 | 1.00x | +0.0% | +0.00 | C |
| gradient-target | 5 | 312.000 vs 305.000 | 0.98x | +23.7% | -0.36 | C |
| gradient-target | 6 | 265.500 vs 305.000 | 1.15x | +0.0% | +0.00 | C |
| noise-target | 0 | 187.500 vs 609.500 | 3.25x | -1.0% | -0.01 | C |
| noise-target | 1 | 235.000 vs 609.500 | 2.59x | -1.0% | -0.01 | C |
| noise-target | 2 | 304.500 vs 609.500 | 2.00x | +57.6% | -0.00 | C |
| noise-target | 3 | 546.500 vs 609.500 | 1.12x | -0.1% | +0.00 | C |
| noise-target | 4 <- current | 609.500 vs 609.500 | 1.00x | +0.0% | +0.00 | C |
| noise-target | 5 | 750.000 vs 609.500 | 0.81x | +0.4% | -0.01 | C |
| noise-target | 6 | 1078.000 vs 609.500 | 0.57x | +0.1% | -0.01 | C |
| d7r2-derived-target | 0 | 54.500 vs 320.500 | 5.88x | +32.9% | -0.60 | A |
| d7r2-derived-target | 1 | 78.000 vs 320.500 | 4.11x | +27.8% | -0.59 | A |
| d7r2-derived-target | 2 | 101.500 vs 320.500 | 3.16x | +6.1% | -0.76 | B |
| d7r2-derived-target | 3 | 367.500 vs 320.500 | 0.87x | -0.0% | -0.13 | C |
| d7r2-derived-target | 4 <- current | 320.500 vs 320.500 | 1.00x | +0.0% | +0.00 | C |
| d7r2-derived-target | 5 | 313.000 vs 320.500 | 1.02x | +1.6% | -0.20 | C |
| d7r2-derived-target | 6 | 422.000 vs 320.500 | 0.76x | -1.1% | -0.13 | C |

## 7. Raw Samples (codec ms in measurement order)

| Case | Method | Samples | Decodable |
|---|---:|---|---|
| gradient-target | 0 | 47,47,31,47,63,63,78,62,62,78,62,62 | True |
| gradient-target | 1 | 94,125,78,78,78,93,94,79,78,78,63,93 | True |
| gradient-target | 2 | 62,125,78,110,109,94,110,94,94,125,78,94 | True |
| gradient-target | 3 | 235,313,281,297,265,281,265,265,265,281,265,297 | True |
| gradient-target | 4 | 250,313,328,329,313,297,328,313,297,297,282,266 | True |
| gradient-target | 5 | 343,297,344,312,313,297,312,312,328,297,312,328 | True |
| gradient-target | 6 | 266,250,250,219,203,265,250,297,281,297,281,297 | True |
| noise-target | 0 | 187,218,234,188,203,187,188,156,172,203,187,187 | True |
| noise-target | 1 | 235,234,250,235,234,235,297,218,250,250,219,218 | True |
| noise-target | 2 | 250,266,313,344,312,328,313,313,297,282,265,250 | True |
| noise-target | 3 | 672,563,516,516,516,546,562,547,594,578,531,515 | True |
| noise-target | 4 | 594,657,610,656,625,610,531,531,563,578,641,609 | True |
| noise-target | 5 | 625,750,687,781,860,656,750,641,765,875,922,625 | True |
| noise-target | 6 | 1062,1078,1110,1032,1000,1453,1578,1078,1016,1047,1359,1234 | True |
| d7r2-derived-target | 0 | 46,63,78,47,62,62,47,47,63,62,46,47 | True |
| d7r2-derived-target | 1 | 78,79,78,62,78,78,78,78,63,93,93,93 | True |
| d7r2-derived-target | 2 | 94,93,125,110,94,93,109,109,125,94,110,94 | True |
| d7r2-derived-target | 3 | 375,359,406,360,391,313,328,297,343,437,438,422 | True |
| d7r2-derived-target | 4 | 328,313,297,344,375,313,344,375,297,359,297,313 | True |
| d7r2-derived-target | 5 | 313,312,313,313,312,406,422,406,438,297,313,391 | True |
| d7r2-derived-target | 6 | 406,437,391,422,468,422,437,453,469,406,360,422 | True |

(Values rounded to integer ms in this table for readability; medians/p95 in
Sections 5-6 use full precision.)

## 8. Quality Equivalence Interpretation

At fixed q70, method changes primarily trade **speed and size**, not fidelity:

- High-detail noise: PSNR is 12.65-12.66 dB for every method (delta <= 0.01 dB)
  and MSE varies by <0.3%. Perceptual/lossy quality at q70 is method-invariant
  here.
- Smooth gradient: method 0 loses 0.62 dB (47.88 vs 48.50) and methods 1-2 lose
  0.44 dB — measurable numerically on a synthetic ramp, but at 47+ dB PSNR this
  is far above any practical visibility threshold for a preview stream.
- Realistic d7r2-derived content: method 0/1 lose ~0.6 dB (38.2 vs 38.8);
  method 2 loses 0.76 dB while also being slower than method 1.

Conclusion: method selection does not meaningfully alter lossy quality at
fixed q70; it is a speed/size dial. This supports choosing the fastest stable
method rather than protecting method 4 for fidelity reasons.

## 9. Production Feasibility (future change only — NOT implemented)

Smallest future code change: route the existing `webp_lossless_compression`
field (or a new sibling effort field) into the **lossy** save call, i.e.
replace the constant `_WEBP_LOSSY_METHOD` with a mapped value in exactly two
places — `comfyapp.py:614` and the duplicated converter `output_converter.py:233`.
Reusing the existing `fast`/`balanced`/`max` vocabulary keeps the contract
surface unchanged (e.g. `fast` -> method 0 for lossy).

Important: today's contract alone is insufficient — setting Preview to an
existing faster mode would have no effect because the lossy branch never
reads `webp_lossless_compression`. A one-line-per-site change is required
first. Any such change must respect the approved product contract (WebP,
quality 70) and should be validated remotely before adoption.

## 10. Batch Parallelism Observation (report only)

`encode_image_tensor_batch` encodes batch items strictly sequentially in a
plain `for batch_idx in range(B)` loop (`comfyapp.py:578`), with independent
per-item PIL saves. The prior E2 lane's batch-of-two gradient total
(390.500 ms) was well under 2x its single-item median (235.000 ms),
hinting at partial overlap already available from libwebp threading/timer
granularity. A small worker pool over batch items is therefore an obvious,
self-contained future optimization opportunity (per-item results are
independent), but it was not designed or implemented here.

## Limitations and Boundaries

- Local Windows CPU run on an AMD host; not a Modal container prediction.
  Remote CPU counts, libwebp builds, and scheduling can differ substantially.
- Cross-session host drift moved this run's method-4 baseline above the
  2026-08-17 recording; within-run comparisons remain valid.
- The uniform-noise case is a deliberate worst-case stress input; production
  generated images resemble the d7r2-derived case more closely.
- Host timer granularity shows coarse steps for short operations; method 0/1
  medians sit well above those steps.
- PSNR/MSE are numeric proxies only; no perceptual-metric package was
  installed (by design).

## Reproduction

From the repository root:

```text
python tests/benchmarks/benchmark_e2_preview_codec_method_local.py --warmups 2 --repetitions 12
```

Files created for this lane:

- `tests/benchmarks/benchmark_e2_preview_codec_method_local.py`
- `PHASE_E2_PREVIEW_CODEC_METHOD_BENCHMARK_2026-08-17.md`

No production source, authoritative test gate, deployment, live Modal run,
GPU spend, or commit was performed.

NOTE (post-E2D): the harness has since been rewritten to sweep the REAL
`webp_lossless_compression` effort argument — the `_WEBP_LOSSY_METHOD`
monkey-patch mechanism above no longer exists and is no longer needed,
because production now maps the effort vocabulary onto the lossy encoder
itself. Sections 1–10 above remain the historical record of the
constant-patching investigation that motivated E2D.

## E2D Production Implementation Verification

Date: 2026-08-22 (run executed 2026-08-22 local, after the E2D source change)
Scope: prove the implemented production path exercises the Preview default
method 0 WITHOUT monkey-patching, and record deterministic local q70 timing.

### What changed in production

The approved Preview path is WebP lossy q70 with fast encoder effort. The
effort rides the existing `webp_lossless_compression` vocabulary and both
production save seams resolve it to the Pillow method via
`contracts.resolve_webp_pillow_method` (`fast`→0, `balanced`→4, `max`→6):

- `comfyapp.py` direct tensor sink: lossy branch saves with the mapped
  method; additive `webp_effort`/`webp_method` diagnostics.
- `output_converter.py` duplicate/post-hoc converter: identical mapping.
- `comfymodal_runtime/contracts.py`: Preview normalization freezes
  `{format: webp_lossy, quality: 70, webp_lossless_compression: fast}` into
  the accepted ExecutionOptions; legacy projection carries it to the remote
  request unchanged (`modal_app.py` needed zero changes).

### Non-monkey-patched proof

The rewritten harness sweeps only the real effort argument and asserts each
arm's observed `webp_method` from the function's own diagnostics. All nine
case x effort arms matched exactly (fast→0, balanced→4, max→6 on gradient,
noise, and d7r2-derived inputs) — the Preview default provably encodes with
method 0 through the unmodified production callable.

### Deterministic local results (q70, 2 warmups + 12 reps)

| Case | Effort | Method | Median ms | P95 ms | Median bytes | PSNR dB | Class |
|---|---|---:|---:|---:|---:|---:|---|
| d7r2-derived-target | fast <- preview default | 0 | 62.000 | 69.750 | 120376 | 38.22 | A |
| gradient-target | fast <- preview default | 0 | 47.000 | 62.450 | 11124 | 47.88 | A |
| noise-target | fast <- preview default | 0 | 171.500 | 194.650 | 1242124 | 12.66 | C |
| d7r2-derived-target | balanced | 4 | 312.000 | 335.200 | 90590 | 38.83 | C |
| gradient-target | balanced | 4 | 219.000 | 255.600 | 6660 | 48.50 | C |
| noise-target | balanced | 4 | 578.000 | 654.400 | 1254562 | 12.66 | C |

Speedup of the new Preview default vs the historical method-4 default:
realistic **5.03x**, gradient **4.66x**, noise **3.37x**. Size delta
+32.9% / +67.0% / -1.0%; PSNR delta -0.60 / -0.62 / -0.01 dB — consistent
with the original investigation's finding that method is a speed/size dial
at fixed q70.

### Verification status

- Effective-method proof table printed by the harness: 9/9 arms ok.
- New `tests/test_e2_preview_effort.py`: 24 passed; E2A/B/C suites remain
  green (57 passed); runtime delivery/contracts/history-save suites green
  (148 passed).
- Local CPU evidence only (same host class as Sections 4–7). Remote actual
  method, `output_codec_ms`, and total live cost remain UNKNOWN until the
  E7 live gate. No deployment, Modal run, GPU spend, or commit was
  performed for E2D.
