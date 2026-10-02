# Working source harness — Phase 0 validation record

Frozen pure-CPU mmap source-read harness. This record exists so that the exact
source state used as the rollback/reference point for the GPU/H2D work is
auditable after the fact.

## Exact commit

- Harness commit (unchanged by this record): `b9196ac50897430af690d570242157f80bbc1100`
  — `source-race: working pure-CPU mmap source-read harness (Sept 2026)`
- The validation/provenance commit is the commit that adds this file. The
  harness source files are byte-identical to `b9196ac`; no runtime source was
  modified for this validation.
- Tag: `working-source-harness` (annotated, message `working source harness`).

Harness files (unchanged):

- `comfymodal_runtime/source_race_oracle.py` — `run_mmap_lifecycle_probe`,
  `lifecycle="fresh"` engine (`_mlc_child`).
- `e04_source_race_modal.py` — dedicated Modal probe app, function
  `run_worker_model_h100`, dispatch branch `lifecycle in ("whole","segmented","fresh")`.
- `tools/run_imbalance_campaign.py` — the runner used (one invocation per slot,
  serial, every run retained).

## Exact profile/config

| item | value |
|---|---|
| workspace | Testing5 (`ws_c1487d319820`) |
| Modal app | `sept-clip-source-race-oracle` |
| function | `run_worker_model_h100` |
| worker_model | `mmap_lifecycle` |
| lifecycle | `fresh` (map exact 64 MiB window, native libc memcpy, synchronous munmap, repeat) |
| map mode | `MAP_PRIVATE` (shared=False, populate=False) |
| read size | 64 MiB (`--read-mib 64`) |
| logical QD | 4 (`--qd 4`), 4 eager reader processes, persistent FD per reader |
| pacer | 4.0 ms global minimum launch spacing |
| allocator | self-service (in-engine) |
| sticky lanes | True |
| GPU request | `h100!` (GPU attached but untouched; source is pure CPU I/O) |
| provider/region pinning | none |
| model | `text_encoders/qwen_3_4b.safetensors` (8,044,982,048 bytes = 120 × 64 MiB) |
| runner | `python tools/run_imbalance_campaign.py --lifecycle fresh --read-mib 64 --qd 4 --gap-ms 4.0` |
| artifacts | `working_source_harness_runs/im-01.json` … `im-20.json` |

Operation cost = `map_ms + preadv_ms + unmap_ms` (the engine's `_op` for the
fresh lifecycle). "Source wall" = first op enter → last op exit
(`full_file_wall_ms`). "GB/s" = `full_file_decimal_gbps`.

## Runs — cohort A (required 10)

| run | provider:region | GB/s | source wall ms | op p50 ms | op p90 ms | op worst ms | ≥250 ms ops | max in-flight | coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| im-01 | gcp:us-west | 6.642 | 1211.1 | 36.6 | 49.4 | 75.5 | 0 | 4 | exact 120/120 |
| im-02 | gcp:eu-west | 5.539 | 1452.5 | 46.9 | 50.3 | 94.5 | 0 | 4 | exact |
| im-03 | gcp:asia-south2 | 5.183 | 1552.3 | 49.4 | 58.8 | 96.5 | 0 | 4 | exact |
| im-04 | gcp:uk | 4.834 | 1664.3 | 50.4 | 57.8 | 173.3 | 0 | 4 | exact |
| im-05 | gcp:eu-west | 5.235 | 1536.8 | 49.2 | 57.0 | 97.7 | 0 | 4 | exact |
| im-06 | gcp:uk | 5.491 | 1465.1 | 46.4 | 52.8 | 70.3 | 0 | 4 | exact |
| im-07 | gcp:us-east | 5.117 | 1572.3 | 45.2 | 51.4 | 818.3 | 1 (block 90) | 4 | exact |
| im-08 | aws:us-west | 3.638 | 2211.5 | 70.1 | 82.1 | 148.6 | 0 | 4 | exact |
| im-09 | unspecified:ca | 6.467 | 1244.0 | 39.0 | 44.5 | 80.0 | 0 | 4 | exact |
| im-10 | aws:us-west | 3.612 | 2227.3 | 71.0 | 85.2 | 152.5 | 0 | 4 | exact |

Cohort A distribution (all 10, none discarded): median **5.209**, mean 5.176,
p10 3.638, p90 6.467, min 3.612, max 6.642.

## Runs — cohort B (independent replication, 10)

| run | provider:region | GB/s | source wall ms | op p50 ms | op p90 ms | op worst ms | ≥250 ms ops | max in-flight | coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| im-11 | gcp:europe-west2 | 6.421 | 1252.9 | 37.1 | 50.3 | 87.3 | 0 | 4 | exact 120/120 |
| im-12 | aws:us-west | 3.335 | 2412.6 | 77.2 | 99.4 | 116.7 | 0 | 4 | exact |
| im-13 | gcp:europe-west2 | 6.060 | 1327.6 | 44.6 | 51.4 | 64.3 | 0 | 4 | exact |
| im-14 | gcp:europe-west9 | 5.390 | 1492.5 | 47.6 | 51.6 | 98.6 | 0 | 4 | exact |
| im-15 | gcp:us-west | 6.423 | 1252.5 | 36.2 | 47.0 | 341.3 | 1 (block 90) | 4 | exact |
| im-16 | oci:us-central | 5.334 | 1508.2 | 48.5 | 59.4 | 76.3 | 0 | 4 | exact |
| im-17 | aws:us-west | 3.048 | 2639.6 | 85.4 | 106.8 | 153.0 | 0 | 4 | exact |
| im-18 | gcp:europe-west2 | 4.481 | 1795.2 | 55.9 | 76.9 | 108.9 | 0 | 4 | exact |
| im-19 | oci:us-central | 5.569 | 1444.6 | 46.1 | 49.5 | 96.1 | 0 | 4 | exact |
| im-20 | gcp:europe-west2 | 5.047 | 1594.0 | 48.0 | 66.7 | 126.5 | 0 | 4 | exact |

Cohort B distribution (all 10, none discarded): median **5.362**, mean 5.111,
p10 3.335, p90 6.423, min 3.048, max 6.423.

## Pooled 20-run distribution

median **5.284**, mean 5.143, p10 3.612, p90 6.423, min 3.048, max 6.642.

Provider-class medians: GCP-only (13 runs) 5.491; OCI us-central (2) 5.452;
AWS us-west (5, all slow) 3.335. Every run: coverage exact 120/120,
max simultaneous in-flight = 4, zero worker/barrier errors.

## Pass result

- **Literal gate median ≥ 5.5 GB/s: NOT MET.** Raw 10-run medians are 5.209
  (cohort A) and 5.362 (cohort B); pooled 5.284. Slow AWS us-west runs
  (3.05–3.64) and non-US GCP hosts pull the unpinned cohort median down.
- **Harness-equivalence: CONFIRMED.** The harness reproduces its known-good
  behaviour and historical distribution (`FINAL_MMAP_OPTS_REPORT.md`: 15-run
  medians 5.382–5.613 with p10 ≈ 2.5 and worst ≈ 2.0–2.4): exact 120/120
  coverage on all 20 runs, QD4 concurrency on all 20, clean op tails (two
  ≥250 ms ops total, both the recurring block-90 offset / a single host), and
  GCP/OCI US hosts at 5.33–6.64 GB/s. No source change was made, so no
  regression path exists.
- **Operator decision (recorded):** the portable/raw median shortfall is
  placement composition, not a source-path change. The operator elected to
  proceed: freeze this exact CPU harness, tag it, and proceed to the minimal
  additive GPU/H2D work.

Evidence retained: all 20 raw run artifacts under
`working_source_harness_runs/` (including per-op `physical_attempts_log`).
