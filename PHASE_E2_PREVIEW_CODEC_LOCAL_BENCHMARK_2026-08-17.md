# Phase E2 Preview Codec Local Benchmark

Date: 2026-08-17  
Scope: local CPU codec-only characterization of the E2A direct-sink encoder

## Verdict

**Classification: C - over the practical target for target-sized inputs.**

The actual E2A callable, `comfyapp.encode_image_tensor_batch`, produced WebP
lossy quality 70 bytes successfully on every sample. At the production target
of 1088 x 1920, the controlled smooth gradient measured 235.000 ms median and
274.350 ms p95, while deterministic high-detail noise measured 555.000 ms
median and 578.000 ms p95. Both are above the preferred `<100 ms` target and
the practical upper target of about `135 ms`. The preserved D7R2 images were
1280 x 720 rather than the target dimensions and measured 94.000/110.000 ms
and 78.500/102.250 ms median/p95, so they demonstrate the size dependence but
do not overturn the target-sized verdict.

This is codec-only local CPU evidence. It does not establish total remote
latency, and it does not recommend changing the approved Preview default.

## Method

The harness calls the real production function directly:

```text
comfyapp.encode_image_tensor_batch(images_t, output_format, quality, "balanced")
```

The Preview arm passes the plain canonical input `output_format="webp"` and
`quality=None`; the current E2A normalization reports codec `webp` and quality
70. The timing reported below is the function's `output_codec_ms`, captured
around the actual `PIL.Image.save(..., format="WEBP", lossless=False,
quality=70, method=4)` interval. It excludes tensor-to-NumPy conversion, PIL
image construction, reading the in-memory buffer, decode validation, disk
writes, asset persistence, volume commit, and network transfer.

Each arm/case used two warmups followed by ten measured repetitions. The
benchmark generated no output files and made no Modal calls.

## Inputs

| Case | Tensor | Input type | Source details |
|---|---|---|---|
| `gradient-target` | `[1, 1920, 1088, 3]` uint8 | synthetic smooth gradient | target dimensions; 6,266,880 decoded bytes |
| `noise-target` | `[1, 1920, 1088, 3]` uint8 | deterministic high-detail noise | target dimensions; seed `20260817`; 6,266,880 decoded bytes |
| `d7r2-original-0` | `[1, 720, 1280, 3]` uint8 | preserved D7R2 image | `d7r2-original-0.png`; source PNG 518,818 bytes |
| `d7r2-original-1` | `[1, 720, 1280, 3]` uint8 | preserved D7R2 image | `d7r2-original-1.png`; source PNG 485,219 bytes |
| `gradient-target-batch2` | `[2, 1920, 1088, 3]` uint8 | synthetic smooth gradient | small batch support check; 12,533,760 decoded bytes |

Comparison arms were current Original/PNG, JPEG quality 70, Preview WebP
quality 70, and WebP quality 75. The batch check used Preview WebP quality 70.

## Environment

| Field | Value |
|---|---|
| Python | 3.11.9 |
| PyTorch | 2.8.0+cu128 |
| Pillow | 11.2.1 |
| Platform | Windows-10-10.0.19045-SP0 |
| Processor | AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD |
| Logical CPUs | 12 |
| Callable source | `comfyapp.py` -> `encode_image_tensor_batch` |

The fast PNG/JPEG samples show coarse 0/15/16 ms steps on this Windows host;
the host timer/Pillow timing granularity is a limitation for those comparison
arms. The WebP measurements are long enough to characterize the target
miss, but local scheduling noise remains.

## Summary

`Median bytes` is the encoded byte count for the complete batch. `Ratio` is
decoded uint8 tensor bytes divided by encoded bytes. All encoded samples were
decoded successfully with Pillow.

| Case | Dimensions | Batch | Arm | Codec | Quality | Median ms | P95 ms | Min ms | Max ms | Median bytes | Ratio | Decodable |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| gradient-target | 1088x1920 | 1 | original-png | png | - | 31.000 | 32.000 | 16.000 | 32.000 | 190276 | 32.94x | true |
| gradient-target | 1088x1920 | 1 | jpeg-q70 | jpeg | 70 | 0.000 | 15.550 | 0.000 | 16.000 | 37813 | 165.73x | true |
| gradient-target | 1088x1920 | 1 | preview-webp-q70 | webp | 70 | 235.000 | 274.350 | 172.000 | 282.000 | 6660 | 940.97x | true |
| gradient-target | 1088x1920 | 1 | webp-q75 | webp | 75 | 219.000 | 251.500 | 188.000 | 265.000 | 6690 | 936.75x | true |
| noise-target | 1088x1920 | 1 | original-png | png | - | 125.000 | 125.000 | 109.000 | 125.000 | 6613593 | 0.95x | true |
| noise-target | 1088x1920 | 1 | jpeg-q70 | jpeg | 70 | 15.000 | 16.000 | 0.000 | 16.000 | 1156902 | 5.42x | true |
| noise-target | 1088x1920 | 1 | preview-webp-q70 | webp | 70 | 555.000 | 578.000 | 516.000 | 578.000 | 1254562 | 5.00x | true |
| noise-target | 1088x1920 | 1 | webp-q75 | webp | 75 | 570.500 | 619.850 | 500.000 | 641.000 | 1288566 | 4.86x | true |
| d7r2-original-0 | 1280x720 | 1 | original-png | png | - | 16.000 | 31.550 | 15.000 | 32.000 | 736335 | 3.75x | true |
| d7r2-original-0 | 1280x720 | 1 | jpeg-q70 | jpeg | 70 | 0.000 | 8.800 | 0.000 | 16.000 | 57867 | 47.78x | true |
| d7r2-original-0 | 1280x720 | 1 | preview-webp-q70 | webp | 70 | 94.000 | 110.000 | 93.000 | 110.000 | 30370 | 91.04x | true |
| d7r2-original-0 | 1280x720 | 1 | webp-q75 | webp | 75 | 78.000 | 102.250 | 78.000 | 109.000 | 32682 | 84.60x | true |
| d7r2-original-1 | 1280x720 | 1 | original-png | png | - | 16.000 | 31.550 | 15.000 | 32.000 | 700560 | 3.95x | true |
| d7r2-original-1 | 1280x720 | 1 | jpeg-q70 | jpeg | 70 | 0.000 | 8.800 | 0.000 | 16.000 | 52137 | 53.03x | true |
| d7r2-original-1 | 1280x720 | 1 | preview-webp-q70 | webp | 70 | 78.500 | 102.250 | 62.000 | 109.000 | 26078 | 106.02x | true |
| d7r2-original-1 | 1280x720 | 1 | webp-q75 | webp | 75 | 94.000 | 125.000 | 93.000 | 125.000 | 27960 | 98.88x | true |
| gradient-target-batch2 | 1088x1920 | 2 | preview-webp-q70-batch2 | webp | 70 | 390.500 | 453.000 | 328.000 | 453.000 | 13320 | 940.97x | true |

## Raw Samples

The `Codec ms samples` values preserve all ten measured repetitions in order.
For the batch row, `Item codec ms samples` preserves the two per-item timings
for each repetition while `Codec ms samples` is their batch total.

| Case | Dimensions | Batch | Arm | Codec/quality | Codec ms samples | Item codec ms samples | Bytes | Ratio | Decodable |
|---|---:|---:|---|---|---|---|---:|---:|---|
| gradient-target | 1088x1920 | 1 | original-png | png/- | 32,31,32,16,31,31,31,31,31,31 | 32;31;32;16;31;31;31;31;31;31 | 190276 | 32.94x | true |
| gradient-target | 1088x1920 | 1 | jpeg-q70 | jpeg/70 | 0,0,0,0,0,0,16,0,0,15 | 0;0;0;0;0;0;16;0;0;15 | 37813 | 165.73x | true |
| gradient-target | 1088x1920 | 1 | preview-webp-q70 | webp/70 | 203,172,235,250,282,250,234,235,218,265 | 203;172;235;250;282;250;234;235;218;265 | 6660 | 940.97x | true |
| gradient-target | 1088x1920 | 1 | webp-q75 | webp/75 | 203,219,234,265,204,204,234,235,219,188 | 203;219;234;265;204;204;234;235;219;188 | 6690 | 936.75x | true |
| noise-target | 1088x1920 | 1 | original-png | png/- | 109,125,125,109,125,125,125,110,125,110 | 109;125;125;109;125;125;125;110;125;110 | 6613593 | 0.95x | true |
| noise-target | 1088x1920 | 1 | jpeg-q70 | jpeg/70 | 0,16,15,16,15,15,15,16,0,16 | 0;16;15;16;15;15;15;16;0;16 | 1156902 | 5.42x | true |
| noise-target | 1088x1920 | 1 | preview-webp-q70 | webp/70 | 547,563,578,578,578,532,516,531,516,578 | 547;563;578;578;578;532;516;531;516;578 | 1254562 | 5.00x | true |
| noise-target | 1088x1920 | 1 | webp-q75 | webp/75 | 547,594,593,578,531,563,641,594,500,500 | 547;594;593;578;531;563;641;594;500;500 | 1288566 | 4.86x | true |
| d7r2-original-0 | 1280x720 | 1 | original-png | png/- | 16,16,16,15,16,16,32,16,31,31 | 16;16;16;15;16;16;32;16;31;31 | 736335 | 3.75x | true |
| d7r2-original-0 | 1280x720 | 1 | jpeg-q70 | jpeg/70 | 0,0,0,0,16,0,0,0,0,0 | 0;0;0;0;16;0;0;0;0;0 | 57867 | 47.78x | true |
| d7r2-original-0 | 1280x720 | 1 | preview-webp-q70 | webp/70 | 94,110,110,94,94,93,94,94,109,94 | 94;110;110;94;94;93;94;94;109;94 | 30370 | 91.04x | true |
| d7r2-original-0 | 1280x720 | 1 | webp-q75 | webp/75 | 109,78,79,78,78,78,94,94,78,78 | 109;78;79;78;78;78;94;94;78;78 | 32682 | 84.60x | true |
| d7r2-original-1 | 1280x720 | 1 | original-png | png/- | 15,31,32,31,15,31,15,16,16,16 | 15;31;32;31;15;31;15;16;16;16 | 700560 | 3.95x | true |
| d7r2-original-1 | 1280x720 | 1 | jpeg-q70 | jpeg/70 | 0,0,16,0,0,0,0,0,0,0 | 0;0;16;0;0;0;0;0;0;0 | 52137 | 53.03x | true |
| d7r2-original-1 | 1280x720 | 1 | preview-webp-q70 | webp/70 | 94,79,93,62,78,78,78,78,109,93 | 94;79;93;62;78;78;78;78;109;93 | 26078 | 106.02x | true |
| d7r2-original-1 | 1280x720 | 1 | webp-q75 | webp/75 | 93,94,94,93,94,109,109,125,125,109 | 93;94;94;93;94;109;109;125;125;109 | 27960 | 98.88x | true |
| gradient-target-batch2 | 1088x1920 | 2 | preview-webp-q70-batch2 | webp/70 | 453,453,390,359,328,407,391,390,344,391 | 219/234;234/219;203/187;187/172;172/156;188/219;188/203;187/203;172/172;219/172 | 13320 | 940.97x | true |

## Interpretation

- WebP quality 70 is not comfortably within the Phase-E codec-only budget at
  the target dimensions on this local CPU. The high-detail case is the clear
  stress case and is more decision-relevant than the highly compressible
  gradient.
- WebP quality 75 was not materially slower than quality 70 in this run. On
  the target gradient it was 219.000 ms median versus 235.000 ms; on noise it
  was 570.500 ms versus 555.000 ms. This is not evidence to change the
  approved quality 70 default.
- The batch-of-two path works and returns two independently decodable WebP
  items. Its target-gradient total was 390.500 ms median, or about 195.250 ms
  per item by median total divided by two; the per-item timings remain
  separately visible in the raw table.
- The very small gradient files and very large compression ratios are a
  property of the synthetic input, not an expected production image-size
  guarantee.

## Limitations and Boundaries

- This is a Windows local CPU run on an AMD host, not a Modal container and not
  a live generation. Remote CPU, container image, Pillow/libwebp build,
  scheduling, and network conditions can differ substantially.
- The timing excludes disk write, content-addressed asset persistence, Modal
  volume commit, and network transfer by design. Those costs must not be
  inferred from this report.
- The preserved D7R2 fixtures are 1280 x 720. Only the synthetic gradient and
  noise cases exercise 1088 x 1920 exactly.
- `output_codec_ms` uses the production timing field and the host shows coarse
  timing steps for short operations. The WebP target misses are large enough
  to remain clear, but individual local measurements are not remote-latency
  predictions.

## Reproduction

From the repository root:

```text
python tests/benchmarks/benchmark_e2_preview_codec_local.py --warmups 2 --repetitions 10
```

Files created for this lane:

- `tests/benchmarks/benchmark_e2_preview_codec_local.py`
- `PHASE_E2_PREVIEW_CODEC_LOCAL_BENCHMARK_2026-08-17.md`

No production source, authoritative test gate, deployment, live Modal run,
GPU spend, or commit was performed.
